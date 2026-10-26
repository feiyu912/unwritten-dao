// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: ANpcViewActor displays authoritative snapshot fields. It does not decide
// location, life, realm, or combat outcomes; movement here is interpolation toward an
// explicit presentation target only.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WorldSyncTypes.h"
#include "NpcViewActor.generated.h"

class UStaticMeshComponent;
class UTextRenderComponent;

UCLASS()
class UNWRITTENDAO_API ANpcViewActor : public AActor
{
	GENERATED_BODY()

public:
	ANpcViewActor();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void Tick(float DeltaSeconds) override;

	/** Bind this actor to the authoritative NPC identified by NpcId. */
	UFUNCTION(BlueprintCallable, Category = "World|View")
	void BindToWorld();

	/** Copy one NPC row into the on-screen label. Never writes back to the server. */
	UFUNCTION(BlueprintCallable, Category = "World|View")
	bool ApplyNpcView(const FWorldNpcView& Npc);

	/** Convenience lookup inside a snapshot projection. */
	UFUNCTION(BlueprintCallable, Category = "World|View")
	bool ApplySnapshot(const FWorldSnapshotView& Snapshot);

	/**
	 * Presentation-only move: projects the point onto the NavMesh (when available) and
	 * interpolates there. This is a visual follow of server state, not a movement decision.
	 */
	UFUNCTION(BlueprintCallable, Category = "World|View")
	void MovePresentationTo(const FVector& WorldLocation);

	UFUNCTION(BlueprintPure, Category = "World|View")
	FString GetDisplayLabel() const { return CurrentLabel; }

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "World|View")
	FString NpcId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World|View")
	bool bPresentationMovement = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "World|View")
	float PresentationSpeed = 220.0f;

	UPROPERTY(BlueprintReadOnly, Category = "World|View")
	FWorldNpcView CurrentNpc;

	UPROPERTY(BlueprintReadOnly, Category = "World|View")
	FString CurrentLabel;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "World|View")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "World|View")
	TObjectPtr<UStaticMeshComponent> BodyMesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "World|View")
	TObjectPtr<UTextRenderComponent> Label;

protected:
	UFUNCTION()
	void HandleSnapshot(const FWorldSnapshotView& Snapshot, bool bFromResync);

private:
	bool bHasPresentationTarget = false;
	FVector PresentationTarget = FVector::ZeroVector;
};