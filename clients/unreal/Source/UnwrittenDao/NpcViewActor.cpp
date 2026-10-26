// Copyright Unwritten Dao. All Rights Reserved.

#include "NpcViewActor.h"

#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "NavigationSystem.h"
#include "UnwrittenDao.h"
#include "WorldSyncSubsystem.h"

ANpcViewActor::ANpcViewActor()
{
	PrimaryActorTick.bCanEverTick = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	SetRootComponent(SceneRoot);

	BodyMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BodyMesh"));
	BodyMesh->SetupAttachment(SceneRoot);
	BodyMesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);

	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(SceneRoot);
	Label->SetRelativeLocation(FVector(0.0f, 0.0f, 220.0f));
	Label->SetHorizontalAlignment(EHorizTextAligment::EHTA_Center);
	Label->SetWorldSize(36.0f);
	Label->SetTextRenderColor(FColor(230, 220, 200));
}

void ANpcViewActor::BeginPlay()
{
	Super::BeginPlay();
	BindToWorld();
}

void ANpcViewActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UWorld* World = GetWorld())
	{
		if (UWorldSyncSubsystem* Sync = World->GetSubsystem<UWorldSyncSubsystem>())
		{
			Sync->OnSnapshotUpdated.RemoveDynamic(this, &ANpcViewActor::HandleSnapshot);
		}
	}
	Super::EndPlay(EndPlayReason);
}

void ANpcViewActor::BindToWorld()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	UWorldSyncSubsystem* Sync = World->GetSubsystem<UWorldSyncSubsystem>();
	if (!Sync)
	{
		return;
	}

	Sync->OnSnapshotUpdated.RemoveDynamic(this, &ANpcViewActor::HandleSnapshot);
	Sync->OnSnapshotUpdated.AddDynamic(this, &ANpcViewActor::HandleSnapshot);

	if (Sync->LatestSnapshot.bValid)
	{
		ApplySnapshot(Sync->LatestSnapshot);
	}
}

bool ANpcViewActor::ApplySnapshot(const FWorldSnapshotView& Snapshot)
{
	const FWorldNpcView* Npc = Snapshot.FindNpc(NpcId);
	if (!Npc)
	{
		UE_LOG(LogUnwrittenDao, Verbose, TEXT("NpcView: '%s' absent from snapshot v%d"),
			*NpcId, Snapshot.StateVersion);
		return false;
	}
	return ApplyNpcView(*Npc);
}

bool ANpcViewActor::ApplyNpcView(const FWorldNpcView& Npc)
{
	CurrentNpc = Npc;
	if (NpcId.IsEmpty())
	{
		NpcId = Npc.NpcId;
	}

	const FString StatusText = Npc.bAlive ? Npc.LocationId : TEXT("DECEASED");
	CurrentLabel = FString::Printf(
		TEXT("%s\nRealm %d / Stage %d\n%s"), *Npc.Name, Npc.Realm, Npc.Stage, *StatusText);

	if (Label)
	{
		Label->SetText(FText::FromString(CurrentLabel));
		Label->SetTextRenderColor(Npc.bAlive ? FColor(230, 220, 200) : FColor(120, 120, 120));
	}
	if (BodyMesh)
	{
		BodyMesh->SetCollisionEnabled(
			Npc.bAlive ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	}
	return true;
}

void ANpcViewActor::HandleSnapshot(const FWorldSnapshotView& Snapshot, bool bFromResync)
{
	ApplySnapshot(Snapshot);
}

void ANpcViewActor::MovePresentationTo(const FVector& WorldLocation)
{
	FVector Target = WorldLocation;
	if (UWorld* World = GetWorld())
	{
		if (UNavigationSystemV1* NavSystem = UNavigationSystemV1::GetCurrent(World))
		{
			FNavLocation Projected;
			if (NavSystem->ProjectPointToNavigation(
					WorldLocation, Projected, FVector(200.0f, 200.0f, 400.0f)))
			{
				Target = Projected.Location;
			}
		}
	}
	PresentationTarget = Target;
	bHasPresentationTarget = true;
}

void ANpcViewActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!bPresentationMovement || !bHasPresentationTarget)
	{
		return;
	}

	const FVector Current = GetActorLocation();
	const FVector Next =
		FMath::VInterpConstantTo(Current, PresentationTarget, DeltaSeconds, PresentationSpeed);
	SetActorLocation(Next, true);

	if (FVector::DistSquared(Next, PresentationTarget) < 4.0f)
	{
		bHasPresentationTarget = false;
	}
}